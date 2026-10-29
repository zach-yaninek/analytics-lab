#!/usr/bin/env python3
"""Slide chart 26 (follow-up to slide 5): is a quick follow-up the same problem, or the machine's usual mix?

Same Category by gap (docs/09 §5 B2, §12 item 4): over every pair of unplanned tickets on one machine, consecutive or
not, both with a recorded Category (No Trouble Found counts; Monitoring excluded), 6,980 pairs, the share whose two
tickets have the same Category, by the days between them, with the 95% account-bootstrap interval as a thin line on
each bar. Blue = 30 days or less apart (the repeat window), light gray = longer gaps, as the legend says; under each
bar its pairs. The dashed line is the pooled share of the pairs more than 90 days apart (908 of 3,137 = 29%): the
machine's usual mix, which a quick follow-up would match if it were unrelated to the ticket before it. The intervals
and the dashed line have a thin white casing, so they read on the blue bars.

The base is not sl_27's: there, Same Category is a class of consecutive repeats, after the Monitoring, No Trouble
Found and blank-Category classes, as a share of all repeats, so the 1-day shares differ (46% here, 32% there).

With 'one_day' in TERMS (a definition followup_terms does not have yet), the 1-day tick carries a dagger and the
definitions say why: pairs that close may include duplicate tickets that were not marked as such (§5 B3).

Input:  verification/outputs/followups/rp_same_by_gap.csv, rp_pairs.csv, followups_summary.json; the interval level
        stated in docs/09 (Intervals)
Output: viz/figures/slides/sl_26_same_problem_by_gap.png (half card, tall)
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib import patheffects as pe  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

import deck_style as S  # noqa: E402
import followup_terms as T  # noqa: E402
from sl_24_repeat_pairings_7d import pct_drawn, pct_text, text_width_pt  # noqa: E402

PNG = 'sl_26_same_problem_by_gap.png'
TERMS = ['pairs_gap', 'label_test', 'interval_line', 'one_day']
DAGGER = '†' if 'one_day' in TERMS else ''   # marks the 1-day bin once its caveat is defined
BINS = ['1 day or less', 'over 1 to 7 days', 'over 7 to 30 days', 'over 30 to 90 days', 'over 90 to 180 days',
        'over 180 days']
TICKS = ['1 day\nor less' + DAGGER, '1–7', '7–30', '30–90', '90–180', '180+']
SHORT = 3                    # the first three bins: 30 days or less (blue)
FAR = 2                      # the last two bins: more than 90 days apart (the usual mix)
MIN_REPEATS = 2              # the label test's machines: 2 or more such repeats (docs/09 §5 B2)
BAR_W = 0.56
Y_TOP = 66                   # the axis runs to 66% so the first bar's label sits above the 60% gridline
LABEL_GAP_IN = 0.08          # inches between the dashed line's end and its label
MIX_LINES = ('usual mix (pairs', '90+ days apart): {}')
CASING = 1.0                 # points of white on each side of the intervals and the dashed line
NUMBER = re.compile(r'\d+(?:[.,]\d+)*')
PROTOCOL = S.ROOT / 'docs' / '09_followups_protocol.md'


def plot(out_dir=S.FIG_DIR):
    d = pd.read_csv(T.FU / 'rp_same_by_gap.csv')
    s = T.summary()
    sh = s['facts']['shuffle']
    n = len(d)
    S.check('sl_26 six gap bins in the protocol order', 1,
            int(d.gap_bin.tolist() == s['definitions']['gap_bins'] == BINS))
    S.check('sl_26 share = same-Category pairs / pairs (every bin)', 0,
            float((d.same_category_pairs / d.pairs - d.share_pairs).abs().max()), 1e-9)
    S.check('sl_26 every interval contains its share', 1,
            int(((d.share_lo <= d.share_pairs) & (d.share_pairs <= d.share_hi)).all()))

    # The usual mix: the pairs more than 90 days apart, pooled (908 of 3,137).
    far = d.tail(FAR)
    S.check('sl_26 usual mix = the bins over 90 days', 1,
            int(far.gap_bin.tolist() == ['over 90 to 180 days', 'over 180 days']))
    usual = far.same_category_pairs.sum() / far.pairs.sum()
    S.check('sl_26 usual mix: 908 same-Category pairs', 908, int(far.same_category_pairs.sum()))
    S.check('sl_26 usual mix: 3,137 pairs', 3137, int(far.pairs.sum()))
    far_from = int(re.search(r'over (\d+) to', far.gap_bin.iloc[0]).group(1))    # 90
    mix_txt = '\n'.join(MIX_LINES).format(pct_text(usual))
    S.check('sl_26 usual-mix label (29%)', 100 * usual, float(re.search(r'(\d+)%', mix_txt).group(1)), 0.5)
    S.check('sl_26 usual-mix label: pairs 90+ days apart', far_from,
            int(re.search(r'(\d+)\+ days apart', mix_txt).group(1)))
    # The tick labels' day counts are the bins' edges ('over 1 to 7 days' -> '1–7').
    for b, tick in zip(d.gap_bin, TICKS):
        S.check(f'sl_26 tick label for {b}', 1, int(re.findall(r'\d+', b) == re.findall(r'\d+', tick)))
    S.check('sl_26 every short-gap share is above the usual mix', 1, int((d.share_pairs.head(SHORT) > usual).all()))
    # The legend's window: the blue bins end at 30 days, where the gray ones start, and a repeat is a next ticket
    # within those 30 days (rp_pairs.csv, one row per eligible index ticket).
    window = int(re.findall(r'\d+', BINS[SHORT - 1])[-1])
    S.check('sl_26 legend: the gray bins start where the blue ones end (30 days)', window,
            int(re.findall(r'\d+', BINS[SHORT])[0]))
    p = pd.read_csv(T.FU / 'rp_pairs.csv')
    S.check('sl_26 legend: the repeat window = 30 days (a repeat = next ticket within 30 days, rp_pairs.csv)', 0,
            int((p.repeat_30 != (p.gap_days <= window)).sum()))

    fig, ax = S.figure(S.HALF_TALL)
    x = np.arange(n)
    x0, x_end = -0.55, n - 0.45                          # the bars' slots; the line's label sits right of x_end
    colour = [S.BLUE if i < SHORT else S.GRAY_LIGHT for i in range(n)]
    bars = ax.bar(x, 100 * d.share_pairs, width=BAR_W, color=colour, linewidth=0, zorder=2)
    mix_line, = ax.plot([x0, x_end], [100 * usual] * 2, color=S.INK2, lw=1.5, ls=(0, (4, 3)),
                        dash_capstyle='butt', zorder=2.5)       # over the bars, under the intervals and labels
    mix_line.set_path_effects([pe.Stroke(linewidth=1.5 + 2 * CASING, foreground=S.WHITE), pe.Normal()])
    intervals, values = [], []
    for i, r in d.iterrows():
        line, = ax.plot([i, i], [100 * r.share_lo, 100 * r.share_hi], color=S.INK, lw=2, solid_capstyle='butt',
                        zorder=3)
        line.set_path_effects([pe.Stroke(linewidth=2 + 2 * CASING, foreground=S.WHITE), pe.Normal()])
        intervals.append(line)
        label = pct_text(r.share_pairs)
        S.check(f'sl_26 {r.gap_bin} label {label}', 100 * r.share_pairs, pct_drawn(label), 0.5)
        hot = i < SHORT
        values.append(ax.annotate(label, xy=(i, 100 * r.share_hi), xytext=(0, 4), textcoords='offset points',
                                  ha='center', va='bottom', fontsize=S.FONT, color=S.INK if hot else S.INK2,
                                  weight='bold' if hot else 'normal', zorder=4))

    # Recessive grid and baseline under the bars only, so the line's label stands on white.
    S.style_axes(ax, grid=None, baseline='bottom')
    ax.spines['bottom'].set_bounds(x0, x_end)
    yticks = np.arange(0, 61, 10)
    ax.hlines(yticks[1:], x0, x_end, color=S.GRID, lw=1.0, zorder=0.5)
    ax.set_ylim(0, Y_TOP)
    ax.set_yticks(yticks)
    S.pct_axis(ax.yaxis)
    ax.set_ylabel('Same Category (% of pairs)')

    # What blue and gray mean (blue is not a test result here, unlike sl_19 and sl_20), above the plot: a figure
    # legend, so the layout keeps it clear of the first bar's label and the y label, however short the axes get.
    handles = [Patch(facecolor=S.BLUE, label=f'{window} days or less apart (the repeat window)'),
               Patch(facecolor=S.GRAY_LIGHT, label=f'more than {window} days apart')]
    legend = fig.legend(handles=handles, loc='outside upper center', ncol=2, handlelength=1.0, handleheight=1.0,
                        handletextpad=0.5, columnspacing=1.4, borderaxespad=0.15, fontsize=S.SMALL)

    # x axis: the gap (two lines at most), then each bin's pairs on a row of its own (minor tick labels, so the x
    # label sits below both rows).
    ax.set_xticks(x)
    ax.set_xticklabels(TICKS, fontsize=S.FONT, color=S.INK, linespacing=1.1)
    counts = [f'{int(v):,}' for v in d.pairs]
    counts[0] += ' pairs'
    for (_, r), txt in zip(d.iterrows(), counts):
        S.check(f'sl_26 {r.gap_bin} pairs ({txt})', r.pairs, int(txt.split()[0].replace(',', '')))
    fig.canvas.draw()
    major_h = max(t.get_window_extent().height for t in ax.get_xticklabels()) * 72 / fig.dpi
    pad = ax.xaxis.get_major_ticks()[0].get_pad()
    ax.xaxis.remove_overlapping_locs = False
    ax.set_xticks(x, minor=True)
    ax.set_xticklabels(counts, minor=True, fontsize=S.SMALL, color=S.INK2)
    ax.tick_params(axis='x', which='minor', length=0, pad=pad + major_h + 3)

    # The dashed line's label, at its right end, in a zone of its own right of the last bar: the axes widen by the
    # label's measured width.
    fig.canvas.draw()
    ax_w_in = ax.get_window_extent().width / fig.dpi
    label_w_in = max(text_width_pt(fig, line.format(pct_text(usual)), S.SMALL) for line in MIX_LINES) / 72
    zone = (LABEL_GAP_IN + label_w_in + 0.02) / ax_w_in  # the label zone, as a fraction of the axes width
    span = (x_end - x0) / (1 - zone)
    ax.set_xlim(x0, x0 + span)
    mix_label = ax.text(x_end + LABEL_GAP_IN / ax_w_in * span, 100 * usual, mix_txt, ha='left', va='center',
                        fontsize=S.SMALL, color=S.INK2, linespacing=1.1, zorder=4)
    # The x label centred under the bars, not under the bars and the label zone.
    ax.set_xlabel('Days between two tickets on the same machine', labelpad=6, x=((x0 + x_end) / 2 - x0) / span)

    check_definitions(d, p, s, usual, far_from, window)
    S.definitions(fig, T.items(TERMS))
    check_layout(fig, ax, mix_label, mix_line, list(bars) + intervals, values, legend)   # reads the final layout
    return [S.save(fig, Path(out_dir) / PNG)]


def check_definitions(d, p, s, usual, far_from, window):
    """The numbers the definitions print, against the data (p: rp_pairs.csv); the patterns fit the current wording
    and the wording asked of followup_terms (the label test's machines and window, the 1-day caveat)."""
    sh = s['facts']['shuffle']
    lab = sh['label_permutation']
    t = T.terms()
    # The test's repeats, recomputed from the pairs table: next ticket within 30 days, a recorded Category on both
    # tickets, neither a monitoring ticket, on the machines with 2 or more such repeats.
    r = p[p.repeat_30]
    r = r[(r.index_category != 'Not categorised') & (r.next_category != 'Not categorised')
          & ~r.index_monitoring & ~r.next_monitoring]
    k = r.groupby('machine_id').size()
    r = r[r.machine_id.isin(k.index[k >= MIN_REPEATS])]
    S.check('sl_26 test pairs recomputed from rp_pairs.csv (833)', sh['pairs'], len(r))
    S.check('sl_26 test matches recomputed from rp_pairs.csv (323)', sh['observed_same'],
            int((r.index_category == r.next_category).sum()))
    S.check('sl_26 test machines recomputed from rp_pairs.csv (299)', sh['machines'], r.machine_id.nunique())
    level = re.search(r'\*\*Intervals:\*\* (\d+)% percentile intervals from ([\d,]+) bootstrap draws',
                      PROTOCOL.read_text())
    S.check('sl_26 the protocol\'s bootstrap draws = the summary\'s', s['n_boot'],
            int(level.group(2).replace(',', '')))

    check_numbers('sl_26', t, 'pairs_gap', [
        ('6,980 pairs = the six bins', r'(\d[\d,]*) pairs', int(d.pairs.sum()), 0),
        ('pairs 90+ days apart = the usual-mix bins', r'(\d+)\+ days apart', far_from, 0)])
    check_numbers('sl_26', t, 'label_test', [
        ('2,000 permutations', r'([\d,]+) times', s['n_perm'], 0),
        ('833 repeats in the test', r'of the ([\d,]+) repeats', sh['pairs'], 0),
        ('repeats: next ticket within 30 days', r'within (\d+) days', window, 0),
        ('299 machines in the test', r'on the ([\d,]+) machines', sh['machines'], 0),
        ('machines with 2 or more such repeats', r'machines with (\d+)(?:\+| or more)', MIN_REPEATS, 0),
        ('39% share it', r'(\d+)% share it', 100 * sh['observed_share'], 0.5),
        ('33% by chance', r'(\d+)% by chance', 100 * lab['null_share'], 0.5),
        ('the p-value as printed', r'\bp ([<=] [\d.]+)', T.p_text(lab['p'], s['n_perm']), None),
        ('the usual-mix line', r'(\d+)% line', 100 * usual, 0.5)])
    check_numbers('sl_26', t, 'interval_line', [
        ('95% interval = the protocol', r'(\d+)% interval', int(level.group(1)), 0),
        ('2,000 bootstrap draws', r'\(([\d,]+) draws\)', s['n_boot'], 0)])
    if 'one_day' in TERMS:
        S.check('sl_26 the 1-day caveat names the dagged bin', 1, int(t['one_day'][0] == BINS[0] + DAGGER))
        check_numbers('sl_26', t, 'one_day', [
            ('1 day or less = the first bin', r'^(\d+) day or less', int(re.findall(r'\d+', BINS[0])[0]), 0)])


def check_numbers(tag, t, key, specs):
    """The numbers in one printed definition ("term: text"), each against the data: specs = [(name, pattern with one
    group, expected, tol)], expected a number, or a string for text such as a p-value. A pattern the wording does not
    match is skipped, but every number printed must be one a pattern matched, so a reworded definition cannot print
    an unchecked number. t: followup_terms.terms()."""
    full = '{}: {}'.format(*t[key])
    covered = []
    for name, pattern, expected, tol in specs:
        m = re.search(pattern, full)
        if m is None:
            continue
        if isinstance(expected, str):
            S.check(f'{tag} definition: {name}', 1, int(m.group(1) == expected))
        else:
            S.check(f'{tag} definition: {name}', expected, float(m.group(1).replace(',', '')), tol)
        covered.append(m.span(1))
    loose = [m.group(0) for m in NUMBER.finditer(full)
             if not any(a <= m.start() and m.end() <= b for a, b in covered)]
    S.check(f'{tag} definition "{t[key][0]}": every number checked' + (f' (not: {", ".join(loose)})' if loose else ''),
            0, len(loose))


def check_layout(fig, ax, mix_label, mix_line, marks, values, legend):
    """On the layout as saved: the dashed line's label clear of every bar, interval and value label, right of the
    line's end and inside the axes; the value labels clear of one another, of the bars and intervals below and of
    the legend."""
    fig.canvas.draw()
    rend = fig.canvas.get_renderer()
    lab = mix_label.get_window_extent(rend)
    marks = [m.get_window_extent(rend) for m in marks]
    vals = [v.get_window_extent(rend) for v in values]
    S.check('sl_26 usual-mix label clear of bars, intervals and value labels', 0,
            sum(lab.overlaps(b) for b in marks + vals))
    S.check('sl_26 usual-mix label right of the dashed line, inside the axes', 1,
            int(mix_line.get_window_extent(rend).x1 < lab.x0 and lab.x1 <= ax.get_window_extent(rend).x1))
    S.check('sl_26 value labels clear of one another', 0,
            sum(a.overlaps(b) for k, a in enumerate(vals) for b in vals[k + 1:]))
    S.check('sl_26 value labels clear of the bars and intervals', 0, sum(v.overlaps(m) for v in vals for m in marks))
    leg = legend.get_window_extent(rend)
    ylab = ax.yaxis.label.get_window_extent(rend)
    S.check('sl_26 legend clear of the value labels, the usual-mix label and the y label', 0,
            sum(leg.overlaps(b) for b in vals + [lab, ylab]))
    S.check('sl_26 legend inside the image', 1, int(leg.x0 >= 0 and leg.x1 <= fig.bbox.x1 and leg.y1 <= fig.bbox.y1))
    S.check('sl_26 y label inside the image, above the x tick labels', 1,
            int(ylab.y1 <= fig.bbox.y1 and ylab.x0 >= 0
                and ylab.y0 >= min(t.get_window_extent(rend).y0 for t in ax.get_xticklabels(which='both'))))


if __name__ == '__main__':
    plot()
