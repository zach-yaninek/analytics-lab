#!/usr/bin/env python3
"""Slide chart 27 (follow-up to slide 5): what the repeats are, by days to the follow-up.

Pairing classes by gap (docs/09 §5 B3): the 1,574 repeats within 30 days, split by the days from the index ticket to
its next ticket (1 day or less, over 1 to 7, over 7 to 30), then all of them, as 100% stacked bars of the pairing
classes (§3.5, the first that applies). The three process classes (a Monitoring ticket, No Trouble Found or a blank
Category involved) are one light-gray segment (followup_terms.CLASS4), outlined in BASE because its fill is close to
white; every segment of 7% or more carries its whole-% share. Rows: the bin and its repeats, under the header 'Days
to the next ticket (repeats)'; the legend sits above.

Same Category here is a class of consecutive repeats, after the process classes, as a share of all repeats, so it is
lower than sl_26's same-Category share of all pairs with a recorded Category (32% against 46% at 1 day or less).

With 'one_day' in TERMS (a definition followup_terms does not have yet), the 1-day row label carries a dagger and the
definitions say why: repeats that quick may include duplicate tickets that were not marked as such (§5 B3).

Input:  verification/outputs/followups/rp_classes.csv, rp_pairs.csv, followups_summary.json
Output: viz/figures/slides/sl_27_repeat_classes.png (half card, tall)
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

import deck_style as S  # noqa: E402
import followup_terms as T  # noqa: E402
from sl_24_repeat_pairings_7d import pct_drawn, pct_text, text_width_pt  # noqa: E402
from sl_26_same_problem_by_gap import check_numbers  # noqa: E402

PNG = 'sl_27_repeat_classes.png'
TERMS = ['classes', 'repeat', 'one_day']
DAGGER = '†' if 'one_day' in TERMS else ''   # marks the 1-day bin once its caveat is defined
BINS = ['1 day or less', 'over 1 to 7 days', 'over 7 to 30 days', 'all repeats']
NAMES = ['1 day or less' + DAGGER, '1 to 7 days', '7 to 30 days', 'All repeats']
HEADER = 'Days to the next ticket (repeats)'
LIGHT_SEG = 'Monitoring, NTF or blank'   # the CLASS4 segment whose fill is close to white
MIN_LABEL = 0.07             # segments of 7% or more carry their share
BAR_H = 0.62                 # bar height, row units
ALL_GAP = 0.45               # extra space above 'All repeats', row units
EDGE = 2.0                   # white gap between segments, points
OUTLINE = 0.8                # BASE outline of the light segment and its legend key, points
TICK_PAD = 6                 # row labels: points left of the plot


def plot(out_dir=S.FIG_DIR):
    c = pd.read_csv(T.FU / 'rp_classes.csv')
    s = T.summary()
    b = s['facts']['part_b']
    classes = s['definitions']['classes']
    S.check('sl_27 the six classes = the summary\'s, each in one slide segment', 1,
            int(sorted(classes) == sorted(T.CLASS4_OF) and set(T.CLASS4_OF.values()) == set(T.CLASS4)))
    S.check('sl_27 the light segment is a CLASS4 segment', 1, int(LIGHT_SEG in T.CLASS4))
    # The six classes only; the direction rows ('Monitoring involved: follow-up only', ...) are left out.
    c6 = c[c.pair_class.isin(classes) & c.gap_bin.isin(BINS)]
    S.check('sl_27 four bins x six classes', len(BINS) * len(classes), len(c6))
    S.check('sl_27 the rows left out are direction rows', 1,
            int(c[~c.pair_class.isin(classes)].pair_class.str.contains(':').all()))
    counts = c6.pivot(index='gap_bin', columns='pair_class', values='pairs').reindex(index=BINS, columns=classes)
    n_bin = c6.groupby('gap_bin').bin_pairs.agg(['min', 'max']).reindex(BINS)
    S.check('sl_27 one bin_pairs per bin', 0, int((n_bin['min'] != n_bin['max']).sum()))
    n_bin = n_bin['min']
    for g in BINS:
        S.check(f'sl_27 {g}: the six classes sum to bin_pairs ({n_bin[g]:,})', n_bin[g], int(counts.loc[g].sum()))
    S.check('sl_27 81 + 550 + 943 = 1,574 (the three bins = all repeats)', n_bin['all repeats'],
            int(n_bin[BINS[:3]].sum()))
    S.check('sl_27 all repeats: each class = the sum over the three bins', 0,
            int((counts.loc[BINS[:3]].sum() - counts.loc['all repeats']).abs().max()))
    S.check('sl_27 all repeats = summary repeats within 30 days (1,574)', b['repeats_30'], int(n_bin['all repeats']))
    S.check('sl_27 1 day or less + 1 to 7 days = summary 7-day repeats (631)', b['repeats_7'],
            int(n_bin[BINS[:2]].sum()))
    S.check('sl_27 all repeats: class shares = summary (30 days)', 0,
            float(max(abs(counts.loc['all repeats', k] / n_bin['all repeats'] - b['class_shares_30'][k])
                      for k in classes)), 1e-6)
    seven = counts.loc[BINS[:2]].sum()
    S.check('sl_27 first two bins: class shares = summary (7 days)', 0,
            float(max(abs(seven[k] / seven.sum() - b['class_shares_7'][k]) for k in classes)), 1e-6)
    # The same counts from the pairs table, one row per eligible index ticket.
    p = pd.read_csv(T.FU / 'rp_pairs.csv')
    rep = p[p.repeat_30]
    ct = pd.crosstab(rep.gap_bin, rep.pair_class).reindex(index=BINS[:3], columns=classes, fill_value=0)
    S.check('sl_27 class counts = rp_pairs.csv, every bin and class', 0,
            int((ct - counts.loc[BINS[:3]]).abs().to_numpy().max()))
    S.check('sl_27 every repeat in one of the three bins', len(rep), int(ct.to_numpy().sum()))

    # The four slide segments.
    c4 = pd.DataFrame({k: counts[[x for x in classes if T.CLASS4_OF[x] == k]].sum(axis=1) for k in T.CLASS4})
    shares = c4.div(c4.sum(axis=1), axis=0)
    S.check('sl_27 every bar sums to 100%', 0, float((shares.sum(axis=1) - 1).abs().max()), 1e-12)

    fig, ax = S.figure(S.HALF_TALL)
    ys = np.array([0, 1, 2, 3 + ALL_GAP])
    labels, segments = [], []
    for y, g in zip(ys, BINS):
        left = 0.0
        for k in T.CLASS4:
            w = 100 * shares.loc[g, k]
            light = k == LIGHT_SEG
            seg = ax.barh(y, w, left=left, height=BAR_H, color=T.CLASS4_COLOR[k],
                          edgecolor=S.BASE if light else 'none', linewidth=OUTLINE if light else 0, zorder=2)[0]
            if left > 0:                         # the white gap between segments, over the light segment's outline
                ax.plot([left, left], [y - BAR_H / 2, y + BAR_H / 2], color=S.WHITE, lw=EDGE,
                        solid_capstyle='projecting', zorder=2.5)
            if shares.loc[g, k] >= MIN_LABEL:
                txt = pct_text(shares.loc[g, k])
                S.check(f'sl_27 {g}: {k} {txt}', 100 * c4.loc[g, k] / n_bin[g], pct_drawn(txt), 0.5)
                labels.append(ax.text(left + w / 2, y, txt, ha='center', va='center_baseline', fontsize=S.SMALL,
                                      color=T.CLASS4_TEXT[k], zorder=3))
                segments.append(seg)
            left += w

    # Row labels: the bin and its repeats; the day counts are the bins' edges.
    row_txt = [f'{name} ({int(n_bin[g]):,})' for name, g in zip(NAMES, BINS)]
    for g, name, txt in zip(BINS, NAMES, row_txt):
        S.check(f'sl_27 row label {txt}', n_bin[g], int(re.search(r'\(([\d,]+)\)$', txt).group(1).replace(',', '')))
        S.check(f'sl_27 row label days for {g}', 1, int(re.findall(r'\d+', g) == re.findall(r'\d+', name)))
    ax.set_yticks(ys)
    ax.set_yticklabels(row_txt)
    ax.tick_params(axis='y', pad=TICK_PAD)
    ax.set_ylim(ys[-1] + 0.5, -0.5)
    ax.set_xlim(0, 100)
    ax.set_xticks([0, 25, 50, 75, 100])
    S.pct_axis(ax.xaxis)
    S.style_axes(ax, grid=None, baseline=None)   # every segment is labelled; a grid would only show between bars
    ax.set_xlabel('Share of repeats')
    # The rows' header, over the row labels: what the days measure and what the count is.
    label_w = max(text_width_pt(fig, x, S.TICK) for x in row_txt) + TICK_PAD
    header = ax.annotate(HEADER, xy=(0, 1), xycoords='axes fraction', xytext=(-label_w, 6),
                         textcoords='offset points', ha='left', va='bottom', fontsize=S.SMALL, color=S.INK2)
    # Legend above the plot, two columns, read left to right in the bars' order; a figure legend, so the layout
    # stacks it above the header. The light key is outlined like its segment.
    handles = [Patch(facecolor=T.CLASS4_COLOR[k], edgecolor=S.BASE if k == LIGHT_SEG else 'none',
                     linewidth=OUTLINE if k == LIGHT_SEG else 0, label=k) for k in T.CLASS4]
    legend = fig.legend(handles=[handles[i] for i in (0, 2, 1, 3)], loc='outside upper center', ncol=2,
                        handlelength=1.0, handleheight=1.0, handletextpad=0.5, columnspacing=1.4, borderaxespad=0.15,
                        fontsize=S.SMALL)

    check_definitions(p, rep, s)
    S.definitions(fig, T.items(TERMS))
    check_layout(fig, ax, labels, segments, header, legend)   # reads the final layout; draws nothing
    return [S.save(fig, Path(out_dir) / PNG)]


def check_definitions(p, rep, s):
    """The numbers the definitions print, against the data (p: rp_pairs.csv; rep: its 30-day repeats); the patterns
    fit the current wording and the wording asked of followup_terms (NTF, the groups, the 1-day caveat)."""
    b = s['facts']['part_b']
    t = T.terms()
    within = int(re.findall(r'\d+', BINS[2])[-1])       # 30: the last bin's edge
    within7 = int(re.findall(r'\d+', BINS[1])[-1])      # 7: the second bin's edge
    S.check('sl_27 a repeat = next ticket within 30 days (rp_pairs.csv)', 0,
            int((p.repeat_30 != (p.gap_days <= within)).sum()))
    S.check('sl_27 a 7-day repeat = next ticket within 7 days (rp_pairs.csv)', 0,
            int((p.repeat_7 != (p.gap_days <= within7)).sum()))
    cutoff = pd.Timestamp(s['definitions']['cutoff'])
    S.check('sl_27 every index ticket opened before the cutoff (rp_pairs.csv)', 1,
            int(pd.to_datetime(p.opened_date).max() < cutoff))
    S.check('sl_27 6,665 eligible index tickets: summary = rp_pairs.csv', b['eligible'], len(p))
    check_numbers('sl_27', t, 'repeat', [
        ('within 30 days = the last bin\'s edge', r'within (\d+) days', within, 0),
        ('7-day = the second bin\'s edge', r'\((\d+)-day', within7, 0),
        ('7-day: within 7 = the second bin\'s edge', r'-day: within (\d+)\)', within7, 0),
        ('before 2 Aug 2026: the cutoff\'s day', r'before (\d+) \w+ \d{4}', cutoff.day, 0),
        ('before 2 Aug 2026: the cutoff\'s month', r'before \d+ (\w+) \d{4}', cutoff.strftime('%b'), None),
        ('before 2 Aug 2026: the cutoff\'s year', r'before \d+ \w+ (\d{4})', cutoff.year, 0),
        ('6,665 eligible index tickets', r'\(([\d,]+)\)', b['eligible'], 0)])
    check_numbers('sl_27', t, 'classes', [])
    groups = re.search(r'request type \(([^)]*)\)', t['classes'][1])
    if groups:                                   # the groups the definition names = those in the three content classes
        named = sorted(re.split(r', (?:or )?| or ', groups.group(1)))
        content = rep[rep.pair_class.isin([k for k, v in T.CLASS4_OF.items() if v != LIGHT_SEG])]
        S.check('sl_27 definition: the groups named = the groups of the content classes', 1,
                int(named == sorted(set(content.index_group) | set(content.next_group))))
    if 'one_day' in TERMS:
        S.check('sl_27 the 1-day caveat names the dagged bin', 1, int(t['one_day'][0] == BINS[0] + DAGGER))
        check_numbers('sl_27', t, 'one_day', [
            ('1 day or less = the first bin', r'^(\d+) day or less', int(re.findall(r'\d+', BINS[0])[0]), 0)])


def check_layout(fig, ax, labels, segments, header, legend):
    """On the layout as saved: every segment label inside its segment, clear of the white gaps; the header above the
    first bar and clear of the legend; the legend inside the image."""
    fig.canvas.draw()
    rend = fig.canvas.get_renderer()
    edge = EDGE * fig.dpi / 72
    inside = []
    for lab, seg in zip(labels, segments):
        a, b = lab.get_window_extent(rend), seg.get_window_extent(rend)
        inside.append(a.x0 >= b.x0 + edge and a.x1 <= b.x1 - edge and a.y0 >= b.y0 + edge / 2
                      and a.y1 <= b.y1 - edge / 2)
    S.check('sl_27 every segment label fits inside its segment', len(inside), sum(inside))
    hd, leg = header.get_window_extent(rend), legend.get_window_extent(rend)
    top_bar = max(sg.get_window_extent(rend).y1 for sg in segments)
    S.check('sl_27 header above the bars, clear of the legend, inside the image', 1,
            int(hd.y0 > top_bar and not hd.overlaps(leg) and hd.x0 >= 0 and hd.x1 <= fig.bbox.x1))
    S.check('sl_27 legend inside the image', 1, int(leg.x0 >= 0 and leg.x1 <= fig.bbox.x1 and leg.y1 <= fig.bbox.y1))


if __name__ == '__main__':
    plot()
