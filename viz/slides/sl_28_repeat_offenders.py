#!/usr/bin/env python3
"""Slide chart 28 (follow-up to slide 5): which models and telemetry types repeat most, and is it more than their
ticket volume and timing give?

Offenders (docs/09 §5 B5, §12 items 4 and 6), in two panels: by model (left) and by telemetry type (right). Rows: the
units with 100+ eligible index tickets, in descending eligible tickets, then the rest pooled ('Other 19 models',
'Other 12 telemetry types': the count is the units pooled); on the right, below a divider, 'No device match' and
'Unknown', which are not telemetry types and are not tested (italic labels, light gray marks). Each row: the share of
its eligible index tickets that repeat within 30 days (blue dot; the x axis says 'index tickets', the word the Repeat
definition defines) with its 95% account-bootstrap interval (blue line), and the rate random timing gives its
machines (open gray ring, B4), drawn under the line so an interval that reaches the ring shows it. The legend names
the interval ('observed, 95% interval'), so the 'Line' definition (repeat_interval) is not printed: 14 rows and the
definitions share the card. Value columns: the row's share of all repeats, and its ratio (observed ÷ random-timing
repeats, relative to the fleet's); in brackets where not tested (the pooled rows, No device match and Unknown). Text
in INK2 as on sl_19 to sl_21. No row differs from the fleet after Benjamini-Hochberg (vs_fleet); one that did would
be drawn blue (above) or navy (below), its ratio in bold, the rest gray, and named in the legend.

Input:  verification/outputs/followups/rp_by_model.csv, rp_by_type.csv, rp_pairs.csv, followups_summary.json
Output: viz/figures/slides/sl_28_repeat_offenders.png (full card, tall)
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import ConnectionPatch  # noqa: E402
from matplotlib.transforms import offset_copy  # noqa: E402

import deck_style as S  # noqa: E402
import followup_terms as T  # noqa: E402
from sl_24_repeat_pairings_7d import pct_drawn, pct_text, text_width_pt  # noqa: E402

PNG = 'sl_28_repeat_offenders.png'
TERMS = ['repeat', 'random_timing', 'repeat_interval', 'srr', 'share_repeats', 'telemetry_type']
PANELS = [('By model', 'rp_by_model.csv', 'model', 'models'),
          ('By telemetry type', 'rp_by_type.csv', 'telemetry_type', 'telemetry types')]
NOT_A_TYPE = 'not a type (not tested)'
TESTED = ('in line', 'above', 'below')
FLAG = {'above': (S.BLUE, 'above the fleet'), 'below': (S.NAVY, 'below the fleet')}
XMAX = 50                     # both panels: 0 to 50%
GAP = 0.4                     # extra row units before the rows that are not telemetry types
PAD_Y = 0.45                  # row units above the first row and below the last
ROW_FONT = S.SMALL            # row labels and value columns: 14 rows share the card with the definitions
DOT = 64                      # marker area, points^2 (about 8 pt across)
X_SHARE, X_RATIO = 52, 104    # value columns: right edges of the digits, points right of the plot
TICK_PAD = 6                  # row labels: points left of the plot
OBSERVED = 'observed, 95% interval'


def check_repeat_term(tag, p):
    """The numbers in the 'repeat' definition (shared with sl_29): within 30 days, 7-day = within 7 (where the
    definition gives it), index tickets opened before 2 Aug 2026, 6,665 of them. p: rp_pairs.csv."""
    s = T.summary()
    m = re.search(r'within (\d+) days (?:\(7-day: within (\d+)\) )?of an (?:eligible )?index ticket opened '
                  r'before (\d+) (\w+) '
                  r'(\d{4}) \(([\d,]+)\)', T.terms()['repeat'][1])
    S.check(f'{tag} definition: within 30 days (every 30-day repeat within 30 days)', 0,
            int((p[p.repeat_30].gap_days > int(m.group(1))).sum()))
    S.check(f'{tag} definition: within 30 days (every later next ticket is not a repeat)', 0,
            int((p[~p.repeat_30].gap_days <= int(m.group(1))).sum()))
    if m.group(2):
        S.check(f'{tag} definition: 7-day = within 7 days', 0,
                int((p.repeat_7 != (p.gap_days <= int(m.group(2)))).sum()))
    cutoff = pd.Timestamp(s['definitions']['cutoff'])
    S.check(f'{tag} definition: before 2 Aug 2026 = the summary cutoff', 1,
            int((cutoff.day, cutoff.strftime('%b'), cutoff.year) == (int(m.group(3)), m.group(4), int(m.group(5)))))
    S.check(f'{tag} definition: every index ticket opened before the cutoff', 1,
            int(pd.to_datetime(p.opened_date).max() < cutoff))
    S.check(f'{tag} definition: 6,665 eligible index tickets', s['facts']['part_b']['eligible'],
            int(m.group(6).replace(',', '')))
    S.check(f'{tag} definition: 6,665 = rows of rp_pairs.csv', len(p), int(m.group(6).replace(',', '')))


def check_telemetry_term(tag, p):
    """The 'telemetry_type' definition (shared with sl_29): the scrubex2.0 types it names are the models it names (99%+
    of each type's tickets in rp_pairs.csv), and No device match and Unknown are the rows that are not types."""
    text = T.terms()['telemetry_type'][1]
    m = re.search(r'(scrubex2\.0)-(\d)((?:, -\d)*,? and -\d|(?:, -\d)+) (?:are|=) ([^;)]+)', text)
    names = [f'{m.group(1)}-{k}' for k in [m.group(2)] + re.findall(r'-(\d)', m.group(3))]
    models = re.split(r', and |, | and ', m.group(4).strip())
    S.check(f'{tag} definition: as many scrubex2.0 types as models', len(names), len(models))
    for ty, model in zip(names, models):
        top = p[p.telemetry_type == ty].model.value_counts(normalize=True)
        S.check(f'{tag} definition: {ty} is {model} (99%+ of its tickets)', 1,
                int(len(top) > 0 and top.index[0] == model and top.iloc[0] >= 0.99))
    bt = pd.read_csv(T.FU / 'rp_by_type.csv')
    S.check(f'{tag} definition: No device match and Unknown are the rows that are not types', 1,
            int(sorted(bt.telemetry_type[bt.vs_fleet == NOT_A_TYPE]) == ['No device match', 'Unknown']
                and 'No device match and Unknown' in text))


def panel_rows(d, unit):
    """[(y, row, kind)]: the units in descending eligible tickets (ties by name), the pooled row, then, after GAP,
    the rows that are not telemetry types; kind is 'unit', 'pooled' or 'not a type'."""
    units = d[~d.pooled & (d.vs_fleet != NOT_A_TYPE)].sort_values(['eligible', unit], ascending=[False, True])
    other = d[~d.pooled & (d.vs_fleet == NOT_A_TYPE)].sort_values(['eligible', unit], ascending=[False, True])
    out = [(float(i), r, 'unit') for i, (_, r) in enumerate(units.iterrows())]
    out += [(float(len(out) + i), r, 'pooled') for i, (_, r) in enumerate(d[d.pooled].iterrows())]
    n = len(out)
    out += [(n + GAP + i, r, 'not a type') for i, (_, r) in enumerate(other.iterrows())]
    return out


def plot(out_dir=S.FIG_DIR):
    s = T.summary()
    b, defs = s['facts']['part_b'], s['definitions']
    p = pd.read_csv(T.FU / 'rp_pairs.csv')
    fleet_oe = b['fleet_observed_over_expected_30']
    S.check('sl_28 rp_pairs: one row per eligible index ticket = summary', b['eligible'], len(p))
    S.check('sl_28 rp_pairs: repeats within 30 days = summary', b['repeats_30'], int(p.repeat_30.sum()))
    S.check("sl_28 fleet's observed ÷ random-timing repeats = rp_pairs", fleet_oe,
            p.repeat_30.sum() / p.null_p30.sum(), 5e-6)

    panels = []
    for title, csv, unit, plural in PANELS:
        d = pd.read_csv(T.FU / csv)
        d['pooled'] = d.pooled.astype(bool)
        rows = panel_rows(d, unit)
        tag = f'sl_28 {title.lower()}'
        S.check(f'{tag}: every row drawn once', len(d), len(rows))
        S.check(f'{tag}: one pooled row', 1, int(d.pooled.sum()))
        S.check(f'{tag}: rows hold every eligible index ticket', b['eligible'], int(d.eligible.sum()))
        S.check(f'{tag}: rows hold every repeat', b['repeats_30'], int(d.repeats_30.sum()))
        S.check(f'{tag}: shares of all repeats sum to 1', 1, float(d.share_of_all_repeats.sum()), 1e-5)
        shown = [r for _, r, k in rows if k == 'unit']
        S.check(f'{tag}: the tested rows have 100+ eligible index tickets', 1,
                int(all(r.eligible >= defs['min_eligible'] for r in shown)))
        S.check(f'{tag}: the tested rows in descending eligible tickets', 1,
                int(all(a.eligible >= c.eligible for a, c in zip(shown, shown[1:]))))
        # The pooled row = every unit under 100 eligible index tickets, recomputed from the pairs (rp_pairs.csv).
        by = p.groupby(unit).agg(eligible=('case_id', 'size'), repeats=('repeat_30', 'sum'),
                                 expected=('null_p30', 'sum'))
        named = set(d[~d.pooled][unit])
        rest = by[~by.index.isin(named)]
        S.check(f'{tag}: the pooled units have under 100 eligible index tickets', 1,
                int((rest.eligible < defs['min_eligible']).all()))
        pooled_name = d[d.pooled][unit].iloc[0]
        by.loc[pooled_name] = rest.sum()
        # The pooled row's label gives the units it holds: 'Other 19 models'.
        label = {r[unit]: r[unit] for _, r, _ in rows}
        label[pooled_name] = f'Other {len(rest)} {plural}'
        S.check(f'{tag}: the pooled row is "Other {plural}"', 1, int(pooled_name == f'Other {plural}'))
        S.check(f'{tag}: row label {label[pooled_name]} = units in rp_pairs without a row of their own', len(rest),
                int(re.search(r'Other (\d+) ', label[pooled_name]).group(1)))
        panels.append((title, unit, d, rows, by, label))
    m_rows, t_rows = panels[0][3], panels[1][3]
    S.check('sl_28 by model: 12 models and Other models', 13, len(m_rows))
    S.check('sl_28 by model: the pooled row is Other models', 1, int(m_rows[-1][1].model == 'Other models'))
    S.check('sl_28 by telemetry type: 11 types, Other telemetry types, No device match, Unknown', 14, len(t_rows))
    S.check('sl_28 by telemetry type: the last rows are Other telemetry types, No device match, Unknown', 1,
            int([r.telemetry_type for _, r, _ in t_rows[-3:]] == ['Other telemetry types', 'No device match',
                                                                   'Unknown']))
    S.check('sl_28 by telemetry type: No device match and Unknown are not tested', 1,
            int(all(r.vs_fleet == NOT_A_TYPE and np.isnan(r.srr_q) for _, r, k in t_rows if k == 'not a type')))

    # Above or below the fleet (B5): none today; a flagged row would be coloured and named in the legend.
    vs = [r.vs_fleet for _, r, _ in m_rows + t_rows]
    flagged = sorted(set(vs) & set(FLAG))
    S.check('sl_28 no model or telemetry type is above or below the fleet (vs_fleet)', 0, len(flagged))
    S.check('sl_28 vs_fleet agrees with the summary (models and types above or below)',
            len(b['models_above'] + b['models_below'] + b['types_above'] + b['types_below']),
            sum(v in FLAG for v in vs))
    base = S.GRAY if flagged else S.BLUE

    fig, ax0 = S.figure(S.FULL_TALL)
    ax0.remove()
    axes = fig.subplots(1, 2)
    fig.get_layout_engine().set(wspace=0.1)
    y_max = max(y for y, _, _ in m_rows + t_rows)
    close = text_width_pt(fig, ')', ROW_FONT)     # a bracketed ratio's ')' hangs right of the digit column
    for ax, (title, unit, d, rows, by, label) in zip(axes, panels):
        tag = f'sl_28 {title.lower()}'
        styles = []
        for y, r, kind in rows:
            name = r[unit]
            rt = f'{tag} {name}'
            # The drawn positions, recomputed from the pairs.
            u = by.loc[name]
            S.check(f'{rt} eligible = rp_pairs', u.eligible, r.eligible)
            S.check(f'{rt} repeats = rp_pairs', u.repeats, r.repeats_30)
            S.check(f'{rt} dot: repeat % = 100 x repeats / eligible', 100 * u.repeats / u.eligible, r.repeat_pct,
                    1e-5)
            S.check(f'{rt} ring: random-timing % = 100 x expected / eligible', 100 * u.expected / u.eligible,
                    r.null_pct, 1e-5)
            S.check(f'{rt} interval contains the repeat %', 1, int(r.repeat_pct_lo <= r.repeat_pct <= r.repeat_pct_hi))
            S.check(f'{rt} every mark inside 0 to {XMAX}%', 1,
                    int(0 < r.repeat_pct_lo and max(r.repeat_pct_hi, r.null_pct) < XMAX))
            if kind == 'not a type':
                mark, ring = S.GRAY_LIGHT, S.GRAY_LIGHT
            else:
                mark, ring = FLAG.get(r.vs_fleet, (base,))[0], S.GRAY
            # Ring under the line (the line shows where the interval reaches the ring), dot on top.
            ax.scatter(r.null_pct, y, s=DOT, facecolor=S.WHITE, edgecolor=ring, linewidth=1.8, zorder=2)
            ax.plot([r.repeat_pct_lo, r.repeat_pct_hi], [y, y], color=mark, lw=2, solid_capstyle='round', zorder=3)
            ax.scatter(r.repeat_pct, y, s=DOT, facecolor=mark, edgecolor=S.WHITE, linewidth=1.5, zorder=4)

            # Value columns: share of all repeats (whole %); ratio (2 dp; in brackets where not tested; bold blue
            # or navy if above or below the fleet).
            share = pct_text(r.share_of_all_repeats)
            S.check(f'{rt} share of all repeats = repeats / all repeats', u.repeats / b['repeats_30'],
                    r.share_of_all_repeats, 1e-6)
            S.check(f'{rt} share label {share}', 100 * r.share_of_all_repeats, pct_drawn(share), 0.5 + 1e-4)
            tested = kind == 'unit'
            ratio = f'{r.srr:.2f}' if tested else f'({r.srr:.2f})'
            S.check(f'{rt} ratio = (repeats / expected) / fleet', u.repeats / u.expected / fleet_oe, r.srr, 1e-5)
            S.check(f'{rt} ratio label {ratio}', r.srr, float(ratio.strip('()')), 0.005)
            S.check(f'{rt} tested = not pooled and a telemetry type', int(tested), int(r.vs_fleet in TESTED))
            S.check(f'{rt} ratio in brackets = not tested', int(not tested), int(ratio.startswith('(')))
            hot = r.vs_fleet in FLAG
            kw = dict(xycoords=('axes fraction', 'data'), textcoords='offset points', ha='right',
                      va='center_baseline', fontsize=ROW_FONT)
            ax.annotate(share, xy=(1, y), xytext=(X_SHARE, 0), color=S.INK2, **kw)
            ax.annotate(ratio, xy=(1, y), xytext=(X_RATIO + (0 if tested else close), 0), **kw,
                        color=FLAG[r.vs_fleet][0] if hot else S.INK2, weight='bold' if hot else 'normal')
            styles.append(kind)

        ax.set_yticks([y for y, _, _ in rows])
        ax.set_yticklabels([label[r[unit]] for _, r, _ in rows], fontsize=ROW_FONT)
        ax.tick_params(axis='y', pad=TICK_PAD)
        for t, kind in zip(ax.get_yticklabels(), styles):
            t.set_color(S.INK2)
            t.set_style('italic' if kind == 'not a type' else 'normal')
        ax.set_ylim(y_max + PAD_Y, -PAD_Y)
        ax.set_xlim(0, XMAX)
        ax.set_xticks(np.arange(0, XMAX + 1, 10))
        S.pct_axis(ax.xaxis)
        S.style_axes(ax, grid='x', baseline=None)
        ax.set_xlabel('Repeat within 30 days (% of index tickets)')

        # The header line: the panel label over the row labels, the column headers over the values.
        label_w = max(text_width_pt(fig, label[r[unit]], ROW_FONT) for _, r, _ in rows) + TICK_PAD
        head = dict(xycoords='axes fraction', textcoords='offset points', va='bottom')
        ax.annotate(title, xy=(0, 1), xytext=(-label_w, 6), ha='left', fontsize=S.FONT, weight='bold', color=S.INK,
                    **head)
        for x, h in ((X_SHARE, 'Share'), (X_RATIO, 'Ratio')):
            ax.annotate(h, xy=(1, 1), xytext=(x, 6), ha='right', fontsize=S.SMALL, color=S.INK2, **head)
        # The divider above the rows that are not telemetry types, across the row labels, plot and values.
        if 'not a type' in styles:
            yd = max(y for y, _, k in rows if k == 'pooled') + 0.5 + GAP / 2
            trans = ax.get_yaxis_transform()
            line = ConnectionPatch(xyA=(0, yd), coordsA=offset_copy(trans, fig=fig, x=-label_w, units='points'),
                                   xyB=(1, yd), coordsB=offset_copy(trans, fig=fig, x=X_RATIO + close,
                                                                    units='points'),
                                   color=S.GRID, lw=1.0, zorder=1)
            line.set_in_layout(False)
            fig.add_artist(line)

    observed = f'{OBSERVED}, in line with the fleet' if flagged else OBSERVED
    handles = [Line2D([], [], color=base, lw=2, marker='o', ms=8, mfc=base, mec=S.WHITE, mew=1.5, label=observed),
               Line2D([], [], ls='', marker='o', ms=8, mfc=S.WHITE, mec=S.GRAY, mew=1.8, label='random timing')]
    handles[1:1] = [Line2D([], [], color=FLAG[f][0], lw=2, marker='o', ms=8, mfc=FLAG[f][0], mec=S.WHITE, mew=1.5,
                           label=FLAG[f][1]) for f in flagged]
    kw = dict(handles=handles, ncol=len(handles), handlelength=1.8, handletextpad=0.5, columnspacing=1.6,
              borderaxespad=0.15, fontsize=S.SMALL)
    if flagged:                 # four entries: a line of their own above the panels
        legend = fig.legend(loc='outside upper center', **kw)
    else:                       # two: in the header line, over the left panel's plot
        legend = axes[0].legend(loc='lower center', bbox_to_anchor=(0.5, 1.0), **kw)

    # The definitions' numbers, and the legend's 95% (the protocol's intervals, docs/09 §6, and the deck's wording).
    t = T.terms()
    m = re.search(r'\*\*Intervals:\*\* (\d+)% percentile intervals from ([\d,]+) bootstrap draws over accounts',
                  (S.ROOT / 'docs' / '09_followups_protocol.md').read_text())
    S.check('sl_28 legend: 95% interval = the protocol\'s intervals (docs/09 §6)', 95, int(m.group(1)))
    S.check('sl_28 legend: the protocol\'s 2,000 draws = the summary\'s', s['n_boot'], int(m.group(2).replace(',', '')))
    S.check('sl_28 legend: 95% interval = the deck\'s repeat-rate interval (repeat_interval)', 95,
            int(re.search(r'(\d+)% interval', t['repeat_interval'][1]).group(1)))
    check_repeat_term('sl_28', p)
    m = re.search(r"fleet's ([\d.]+): (none differs)?.*?q < ([\d.]+)\)", t['srr'][1])
    S.check("sl_28 definition: the fleet's 1.53", fleet_oe, float(m.group(1)), 0.005)
    S.check('sl_28 definition: none differs = no row above or below', int(not flagged), int(bool(m.group(2))))
    S.check('sl_28 definition: q < 0.05 = the protocol alpha', defs['alpha'], float(m.group(3)))
    if 'in brackets' in t['srr'][1]:          # the wording asked for: brackets = not tested, as drawn
        tail = t['srr'][1].split('in brackets', 1)[1]
        S.check('sl_28 definition: in brackets = not tested, the pooled and light-gray rows', 1,
                int('not tested' in tail and 'pooled' in tail and 'light-gray' in tail))
    m = re.search(r'of all ([\d,]+) repeats; models \(or types\) with (\d+)\+ (?:eligible )?index',
                  t['share_repeats'][1])
    S.check('sl_28 definition: 1,574 repeats', b['repeats_30'], int(m.group(1).replace(',', '')))
    S.check('sl_28 definition: 100+ eligible index tickets', defs['min_eligible'], int(m.group(2)))
    m = re.search(r'bootstrap over accounts \(([\d,]+) draws\)', t['share_repeats'][1])
    if m:                                     # the wording asked for gives the intervals' bootstrap here
        S.check('sl_28 definition: 2,000 bootstrap draws', s['n_boot'], int(m.group(1).replace(',', '')))
    check_telemetry_term('sl_28', p)
    S.definitions(fig, T.items(TERMS))
    check_layout(fig, axes, legend)               # reads the final layout; draws nothing
    return [S.save(fig, Path(out_dir) / PNG)]


def check_layout(fig, axes, legend):
    """On the layout as saved: the panel labels, column headers and value columns inside the image; the legend
    inside it and clear of the header line's text; neighbouring row labels clear of each other."""
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    box = fig.bbox
    texts = [t for ax in axes for t in ax.texts]
    inside = [t.get_window_extent(r) for t in texts]
    S.check('sl_28 panel labels, column headers and values inside the image', len(inside),
            sum(b.x0 >= box.x0 and b.x1 <= box.x1 and b.y0 >= box.y0 and b.y1 <= box.y1 for b in inside))
    leg = legend.get_window_extent(r)
    S.check('sl_28 legend inside the image, clear of the panel labels and column headers', 1,
            int(leg.x0 >= box.x0 and leg.x1 <= box.x1 and leg.y1 <= box.y1
                and not any(leg.overlaps(b) for b in inside)))
    for ax in axes:
        title = next(t.get_text() for t in ax.texts if t.get_text().startswith('By '))
        ext = sorted((t.get_window_extent(r) for t in ax.get_yticklabels() if t.get_text()), key=lambda b: -b.y0)
        S.check(f'sl_28 {title.lower()}: neighbouring row labels clear of each other', 0,
                sum(a.y0 < b.y1 for a, b in zip(ext, ext[1:])))


if __name__ == '__main__':
    plot()
